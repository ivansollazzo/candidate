"""Background LLM tasks (job posting and CV filling), kept in memory until the frontend reads them."""

import logging
import threading
import uuid
from collections import OrderedDict
from collections.abc import Callable
from dataclasses import dataclass, field

from app.i18n import t
from app.models import TaskStatus
from app.services.llm import LLMError

log = logging.getLogger(__name__)

MAX_TASKS = 50


@dataclass
class AITask:
    user_id: int
    id: str = field(default_factory=lambda: uuid.uuid4().hex)
    status: TaskStatus = TaskStatus.PENDING
    result: dict | None = None
    error: str | None = None


_tasks: OrderedDict[str, AITask] = OrderedDict()
_lock = threading.Lock()


def create(user_id: int) -> AITask:
    task = AITask(user_id)
    with _lock:
        _tasks[task.id] = task
        while len(_tasks) > MAX_TASKS:
            _tasks.popitem(last=False)
    return task


def get(task_id: str) -> AITask | None:
    with _lock:
        return _tasks.get(task_id)


def run(task: AITask, fn: Callable[..., dict], *args) -> None:
    task.status = TaskStatus.RUNNING
    try:
        task.result = fn(*args)
        task.status = TaskStatus.DONE
    except LLMError as exc:
        task.error = str(exc)
        task.status = TaskStatus.FAILED
    except Exception:
        log.exception("LLM task failed")
        task.error = t("task_failed")
        task.status = TaskStatus.FAILED
