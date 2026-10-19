# Candidate

Candidate is a self-hosted web app for keeping track of your job applications. It stores every application with its
status, dates, events and notes, keeps your professional profile, and tells you how well your skills match each
position.

Forms can be filled in by hand or with a local language model (Qwen 3 4B served by Ollama) that reads a job posting or
your CV and fills in the fields for you. Everything runs on your machine: no data leaves it, and no external AI service
is used.

Version 1.1 (build 20261019.1752), by Ivan Sollazzo.

## Features

- **Applications**: list with search, status filter (applied, interview, offer, inactive, rejected, completed) and a
  saved sort order (date applied, status, name, latest event), and a detail
  page with job details, salary, requirements and status history.
- **AI fill (optional)**: paste a job posting, give a link or upload a PDF, DOCX or TXT file, and the model fills in
  the form. Empty fields are filled straight away; fields you already filled are only replaced if you confirm. Nothing
  is saved until you press Save.
- **Profile**: personal details, experience, education, projects, certifications and skills, filled in by hand or
  from your CV. Technologies used in projects and experience are added to your skills automatically.
- **Skill match**: for every application, a score with matching, partial and missing skills, plus optional advice on
  where to improve.
- **Agenda**: interviews, calls, emails, follow-ups and notes for each application, with overdue and upcoming events
  at a glance.
- **Multi-user**: sign-in, admin and user roles, password recovery keys (no email needed), configurable password and
  lockout policy.
- **Updates from the app**: pick a branch of the repository and install its version when it is newer than the
  installed one.
- **Italian and English** interface, light and dark theme.

## Requirements

- [Docker](https://docs.docker.com/get-docker/) with Docker Compose (Docker Desktop on macOS and Windows).
- About 4 GB of free RAM for the language model, and about 5 GB of disk space for images and models.
- Optional GPU acceleration on Linux and Windows (see [Hardware acceleration](#hardware-acceleration)).

Nothing else needs to be installed on the host.

## Installation

```bash
git clone <repository-url> candidate
cd candidate
docker compose up --build
```

Then open http://localhost:5173.

On first start:

1. The setup wizard asks for the language, creates the administrator account and shows its **recovery key**. Keep it
   somewhere safe: it is the only way to reset the password.
2. You choose whether to enable the AI features, then fill in your profile and, if you like, your first application.

The first start downloads the language model (about 2.5 GB). The embedding model used for skill matching (about
470 MB) is downloaded the first time a match is computed. Settings › System shows when the model is ready.

### Stopping and removing

| Command | Effect |
|---|---|
| `Ctrl+C` or `docker compose stop` | Stops the app. Data and downloaded models are kept. |
| `docker compose down` | Removes the containers. Data and downloaded models are kept. |
| `docker compose down -v` | Also removes the database, uploaded files and the embedding model. |
| `docker volume rm candidate_ollama` | Removes the downloaded language model (the prefix is the project folder name). |

The Ollama container is created by the `llm` service and removed whenever the app stops. The `updates` volume only
holds the update status.

### Updating

Settings › Updates (admin only) lists the branches of the repository with the version each one contains. There you
choose the branch to follow (by default the one in use) and how often to check it (every hour, 6 or 12 hours, daily,
weekly or only on request). When the followed branch has a newer version, a dot appears on the settings icon and the
version can be installed. A version is installed only if it is newer than the installed one, so the database is never
taken back to an older schema: following a branch with an older version simply waits until it gets a newer one.

Installing a version is handled by the `updater` service: it checks out the branch, rebuilds the backend and frontend
while the current version keeps running, replaces them and removes the old images. The app shows an "Updating" screen
and reloads by itself when the new version is up. If the build fails, the previous version stays in use.

This needs a folder created with `git clone`. The updater manages that folder: it always moves it to the branch on
GitHub, so you never have to pull or commit there. If tracked files were changed locally, they are set aside with
`git stash` (see `git stash list`) instead of blocking the update; untracked files such as `.env` and
`docker-compose.override.yml` are never touched, so that is where your own settings go (see
[Your own changes](#your-own-changes-docker-composeoverrideyml)). Develop in a separate copy. When an update also
changes `docker-compose.yml`, `llm/` or `updater/`, the app asks you to run `docker compose up --build -d` once to
apply it.

You can always update by hand:

```bash
git pull
docker compose up --build -d
```

Database migrations run automatically when the backend starts.

## Configuration

Most settings are changed from the app: language and theme (per user), AI features on or off, hardware acceleration,
password and lockout policy, and users (admin only).

### Docker Compose variables

Set them in a `.env` file next to `docker-compose.yml` (or in the shell):

| Variable | Default | Description |
|---|---|---|
| `LLM_MODEL` | `qwen3:4b` | Ollama model to use. `qwen3:1.7b` is about twice as fast but less accurate. |
| `OLLAMA_PORT` | *(unset)* | Publishes Ollama on `127.0.0.1:<port>`, for running the backend outside Docker. |

Example: `LLM_MODEL=qwen3:1.7b docker compose up --build`

### Your own changes: docker-compose.override.yml

Don't edit `docker-compose.yml`: it belongs to the repository and every update replaces it with the version of the
branch (your edits are kept in a `git stash`, but no longer applied). Put your changes in a
`docker-compose.override.yml` next to it instead: Docker Compose merges it automatically on every `docker compose`
command, and Git and the updater never touch it.

Lists such as `ports` and `volumes` are added to the ones in `docker-compose.yml`; to replace them, tag them with
`!override`. For example, to keep the data in folders of your choice (bind mounts) instead of Docker volumes:

```yaml
services:
  db:
    volumes: !override
      - ./data/postgres:/var/lib/postgresql/data
  backend:
    volumes: !override
      - ./data/backend:/app/data
      - llm-runtime:/runtime
      - updates:/updates
```

Keep the entries you don't change (here `llm-runtime` and `updates`), since `!override` replaces the whole list.
To move existing data, stop the app and copy it out of the volumes first.

### Ports

| Port | Service |
|---|---|
| `5173` | Web app |
| `8000` | REST API, with interactive documentation at http://localhost:8000/docs |
| `5432` | PostgreSQL |

To change a port, override it in `docker-compose.override.yml`:

```yaml
services:
  frontend:
    ports: !override
      - "8080:5173"
```

### Backend variables

The backend reads these environment variables, or `backend/.env` when it runs outside Docker (see
`backend/.env.example`). In Docker, add them to the `environment` section of the `backend` service in
`docker-compose.override.yml`.

| Variable | Default | Description |
|---|---|---|
| `DATABASE_URL` | `postgresql+psycopg://candidate:candidate@localhost:5432/candidate` | PostgreSQL connection string. |
| `LLM_PROVIDER` | `ollama` | `auto` uses the model started by the `llm` service (the Docker setting); `ollama` uses `LLM_BASE_URL` and `LLM_MODEL`. |
| `LLM_BASE_URL` | `http://localhost:11434` | Ollama address, with `LLM_PROVIDER=ollama`. |
| `LLM_MODEL` | `qwen3:4b` | Model name, with `LLM_PROVIDER=ollama`. |
| `LLM_TIMEOUT_SECONDS` | `600` | Maximum time for a single model request. |
| `LLM_NUM_CTX` | `8192` | Model context size in tokens. |
| `EMBEDDING_MODEL` | `intfloat/multilingual-e5-small` | Sentence-transformers model for skill matching. |
| `MATCH_THRESHOLD` | `0.90` | Similarity above which a skill counts as a match. |
| `PARTIAL_MATCH_THRESHOLD` | `0.85` | Similarity above which a skill counts as a partial match. |
| `UPLOAD_DIR` | `data/uploads` | Where CVs, job posting files and profile photos are stored. |
| `MAX_UPLOAD_MB` | `10` | Maximum upload size. |
| `CORS_ORIGINS` | `["http://localhost:5173", "http://127.0.0.1:5173"]` | Origins allowed to call the API (JSON list). |

The match thresholds are a starting point. You can tune them by looking at the `similarity` values returned by
`GET /api/applications/{id}/match`.

## Hardware acceleration

The `llm` service detects the available hardware and starts Ollama with the best option, in this order:

| Hardware | Acceleration | Host requirements |
|---|---|---|
| NVIDIA GPU | CUDA | NVIDIA Container Toolkit (Linux) or Docker Desktop with WSL2 (Windows) |
| AMD GPU | ROCm | ROCm drivers (Linux) |
| Intel or AMD GPU without ROCm, integrated GPUs included | Vulkan | Drivers with Vulkan support (Linux) |
| Anything else | CPU | none |

Hardware acceleration is not currently supported on Mac, where the model runs on the CPU. Settings › System shows
which options work on your machine and lets you pick one instead of the automatic choice; if it fails, Ollama falls
back to the CPU.

With the 4B model, each extraction step takes roughly 30 to 60 seconds on a modern 8-core CPU, so a job posting or a
CV can take a few minutes. A GPU is much faster. The work runs in the background, so you can keep using the app.

If you don't need the AI features, turn them off in Settings › System: the model is stopped and its memory freed, and
everything else, skill matching included, keeps working.

## Development

Run the database and the model in Docker, and the backend and frontend on the host:

```bash
OLLAMA_PORT=11434 docker compose up -d db llm

# Backend
cd backend
python -m venv .venv && source .venv/bin/activate
pip install -r requirements-dev.txt
cp .env.example .env
alembic upgrade head
uvicorn app.main:app --reload

# Frontend, in another terminal
cd frontend
npm install
npm run dev
```

Backend tests need an empty `candidate_test` database; the model and embeddings are mocked:

```bash
createdb -h localhost -U candidate candidate_test
cd backend && pytest
```

### Project structure

```
backend/     FastAPI app (app/api, app/services), SQLModel models, Alembic migrations, tests
frontend/    React + TypeScript app (src/pages, src/components, src/lib)
llm/         Service that detects the hardware and manages the Ollama container
updater/     Service that installs new versions from the Git repository
```

## Built with

FastAPI, SQLModel, Alembic, PostgreSQL · React, TypeScript, Vite, Tailwind CSS, TanStack Query, Lucide · Ollama,
Qwen 3 4B, sentence-transformers (multilingual-e5-small) · pdfplumber, python-docx, trafilatura · pwdlib (Argon2),
PyJWT, Pillow · Docker Compose.

Thanks to the open source projects Candidate is built on.
