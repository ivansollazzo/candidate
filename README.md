# Candidate

Candidate is a self-hosted web app for keeping track of your job applications. It stores every application with its
status, dates, events, notes and attached files, keeps your professional profile, and tells you how well your skills match each
position.

Forms can be filled in by hand or with a local language model (Qwen 3 4B served by Ollama) that reads a job posting or
your CV and fills in the fields for you. Everything runs on your machine: no data leaves it, and no external AI service
is used.

Version 2.0 (build 20261102.1448), by Ivan Sollazzo.

## Features

- **Applications**: list with search, status filter (applied, interview, offer, inactive, rejected, completed),
  sort order (date applied, status, name, latest event), both saved per user, multiple selection to change the
  status of or delete several applications at once, the match score of each application when its report
  exists, and a detail page with job details, salary, requirements and status history.
- **Attachments**: attach any files to an application (cover letter, offer, test...), up to 10 MB each. They are
  deleted from disk together with the application.
- **AI fill (optional)**: paste a job posting, give a link or upload a PDF, DOCX or TXT file: the application is saved
  right away and the model fills in its fields in the background. Filling an application or the profile again fills
  the empty fields and proposes the different values for the ones you already filled, applied only if you confirm.
  A checkbox on the new application page, saved per user, also generates the match report once the fields are
  filled.
- **Background operations**: AI fills and match reports are queued and run one at a time as soon as the model is
  free, so a slow machine works through them while you do something else, also after leaving the page or a restart.
  The operations button in the header lists them with their place in the queue: each one can be cancelled (a new
  application not filled in yet is deleted, a report goes back to the previous one, the model stops right away), and
  a notice appears when one is done.
- **Profile**: personal details, experience, education, projects, certifications and skills, filled in by hand or
  from your CV. Technologies used in projects and experience are added to your skills automatically.
- **Match report (AI)**: on request, the local model compares an application's skills with your profile and returns
  a score, matching, partial and missing skills with a short reason each, and advice on where to improve. It works for
  any job, not only tech. Soft skills are listed apart and don't count in the score. When the skills of the profile or
  of the application change, the report suggests regenerating it. Reports exist only with AI on: turning AI off
  deletes them.
- **Agenda**: interviews, calls, emails, follow-ups and notes for each application, with an optional start and end
  time, and overdue and upcoming events at a glance.
- **Overview**: widgets to move, resize, add and remove with the brush button, saved per user: counters by status,
  calendar, upcoming events, recent applications, profile, applications per week, best matches, reports to
  regenerate, skills missing most often and applications with no news for two weeks.
- **Multi-user**: sign-in, admin and user roles, password recovery keys (no email needed), configurable password and
  lockout policy.
- **Updates from the app**: follow the stable or beta channel, or a branch, and install a newer version with one
  click. Ready-made images are downloaded from GitHub, the database is saved first, and if the new version doesn't
  start everything goes back as it was. An update can be installed only when no AI operation is queued or running,
  and none starts until it is over.
- **Italian and English** interface, light and dark theme.

## Requirements

- [Docker](https://docs.docker.com/get-docker/) with Docker Compose (Docker Desktop on macOS and Windows).
- About 4 GB of free RAM for the language model, and about 5 GB of disk space for images and models.
- Optional GPU acceleration on Linux and Windows (see [Hardware acceleration](#hardware-acceleration)).

Nothing else needs to be installed on the host.

## Installation

```bash
git clone https://github.com/ivansollazzo/candidate.git
cd candidate
docker compose up -d
```

Docker Compose downloads the images published on GitHub Container Registry, so nothing is built on your machine.
Then open http://localhost:5173.

On first start:

1. The setup wizard asks for the language, creates the administrator account and shows its **recovery key**. Keep it
   somewhere safe: it is the only way to reset the password.
2. You choose whether to enable the AI features, then fill in your profile and, if you like, your first application.

The first start downloads the language model (about 2.5 GB). Settings › System shows when the model is ready.

### Stopping and removing

| Command | Effect |
|---|---|
| `Ctrl+C` or `docker compose stop` | Stops the app. Data and downloaded models are kept. |
| `docker compose down` | Removes the containers. Data and downloaded models are kept. |
| `docker compose down -v` | Also removes the database and uploaded files. |
| `docker volume rm candidate_ollama` | Removes the downloaded language model (the prefix is the project folder name). |

The Ollama container is created by the `llm` service and removed whenever the app stops. The `updates` volume only
holds the update status.

### Updating

Every push to the repository builds the images of all services for amd64 and arm64 with GitHub Actions
(`.github/workflows/images.yml`) and publishes them on GitHub Container Registry, tagged with the commit
(`sha-<commit>`), the branch and, for release tags, the tag plus `latest` (releases such as `v2.1`) or `beta` (all
tags, pre-releases such as `v2.1-beta.1` included).

Settings › Updates (admin only) shows the installed version and lets you choose where updates come from:

- **Stable**: the newest release (the default).
- **Beta**: the newest release or pre-release.
- **A branch**: its latest commit, for testing work in progress.

When the chosen channel or branch has a newer version and its images are published, a dot appears on the settings
icon and the version can be installed. A version is installed only if it is newer than the installed one, so the
database is never taken back to an older schema. Right after a push the images take a few minutes to build: until
they are published, the new version is shown as "being prepared". You also choose how often to check (every hour, 6
or 12 hours, daily, weekly or only on request).

Installing is handled by the `updater` service:

1. It saves a dump of the database to the `updates` volume (`database-before-update.sql`).
2. It writes the `docker-compose.yml` of the new version and `CANDIDATE_TAG=sha-<commit>` in `.env` (only that line
   changes), then downloads the images. The app stays usable, with a progress bar under the header.
3. It recreates the services. The app shows an "Updating" screen and reloads by itself when the new version is up.
4. It waits for the backend to answer with the new build, database migrations included. If it doesn't within five
   minutes, it puts back the previous `docker-compose.yml`, `.env` and database and starts the previous version again;
   the Updates tab shows the backend log.
5. It removes the images of the previous version and, when its own image changed, replaces its own container.

An update can't be installed while AI operations are queued or running, and none starts until it is over.

If GitHub can't be reached, a check gives up after a minute: the tab keeps showing the versions of the last
successful check with an error message, and the updater tries again after 15 minutes (or at the next interval, if
shorter). Docker sets a container's DNS servers when it starts: if the server's change later (a new DHCP lease, a VPN),
the updater can no longer resolve GitHub, so when a check fails that way it restarts its own container (at most once
every 15 minutes).

The updater needs the Docker socket, which gives it full control of Docker on the host, like the `llm` service.

You can always update by hand, choosing the version in `.env` (`CANDIDATE_TAG=latest`, `beta`, a branch name or
`sha-<commit>`):

```bash
docker compose pull
docker compose up -d
```

Database migrations run automatically when the backend starts.

### Building from source and forks

`docker compose up --build` builds the images from the folder instead of downloading them, and so does `docker compose
up` when no image is published for `CANDIDATE_TAG`. A fork publishes its own images with the same workflow: set
`CANDIDATE_REPOSITORY=<owner>/<repository>` (lowercase) in `.env` to use them and to update from the fork. On GitHub,
make the packages public (package settings › Change visibility) so that installations can download them without
signing in.

## Configuration

Most settings are changed from the app: language and theme (per user), AI features on or off, hardware acceleration,
password and lockout policy, and users (admin only).

### Docker Compose variables

Set them in a `.env` file next to `docker-compose.yml` (or in the shell):

| Variable | Default | Description |
|---|---|---|
| `CANDIDATE_TAG` | `latest` | Version of the images: `latest`, `beta`, a branch name or `sha-<commit>`. Written by the updater. |
| `CANDIDATE_REPOSITORY` | `ivansollazzo/candidate` | GitHub repository of the images and of the updates, for a fork. |
| `LLM_MODEL` | `qwen3:4b` | Ollama model to use. `qwen3:1.7b` is about twice as fast but less accurate. |
| `OLLAMA_PORT` | *(unset)* | Publishes Ollama on `127.0.0.1:<port>`, for running the backend outside Docker. |

Example: `LLM_MODEL=qwen3:1.7b docker compose up -d`

### Your own changes: docker-compose.override.yml

Don't edit `docker-compose.yml`: every update replaces it with the one of the new version. Put your changes in a
`docker-compose.override.yml` next to it instead: Docker Compose merges it automatically on every `docker compose`
command, and the updater never touches it.

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
| `UPLOAD_DIR` | `data/uploads` | Where CVs, profile photos and application attachments are stored. |
| `MAX_UPLOAD_MB` | `10` | Maximum upload size. |
| `CORS_ORIGINS` | `["http://localhost:5173", "http://127.0.0.1:5173"]` | Origins allowed to call the API (JSON list). |

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
everything else keeps working. Match reports need the model, so turning AI off deletes them.

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

Backend tests need an empty `candidate_test` database; the model is mocked:

```bash
createdb -h localhost -U candidate candidate_test
cd backend && pytest
```

### Project structure

```
backend/     FastAPI app (app/api, app/services), SQLModel models, Alembic migrations, tests
frontend/    React + TypeScript app (src/pages, src/components, src/lib)
llm/         Service that detects the hardware and manages the Ollama container
updater/     Service that installs new versions from the images on GitHub Container Registry
.github/     Workflow that builds and publishes the images
```

## Built with

FastAPI, SQLModel, Alembic, PostgreSQL · React, TypeScript, Vite, Tailwind CSS, TanStack Query, Lucide · Ollama,
Qwen 3 4B · pdfplumber, python-docx, trafilatura · pwdlib (Argon2),
PyJWT, Pillow · Docker Compose.

Thanks to the open source projects Candidate is built on.
