# Code Quiz — Python Quiz Application

A Flask-based web application for timed, category-based quizzes. Participants can answer randomly selected questions, receive scores with configurable negative marking, review explanations, and compare results on a leaderboard. Administrators can manage questions and quiz settings through a protected dashboard.


## Live Demo

**Live Application:** [Code Quiz](https://quiz-application-s8w3.onrender.com)  




## Project Information

| Field | Details |
|---|---|
| Application | [Code Quiz](https://quiz-application-s8w3.onrender.com)  |
| Author | Pritam Rabha |
| Programme | MCA, 3rd Semester |
| Course | Python Programming |
| Project Guide | Dr. Pangambam Sendash Singh |
| Institution | Dr. Hari Singh Gour Vishwavidyalaya, Sagar, Madhya Pradesh |
| Copyright | Copyright © 2026 Pritam Rabha. All rights reserved. |

> **Academic disclaimer:** Code Quiz is an independent academic project developed for educational purposes. It is not an official application of, or endorsed by, Dr. Hari Singh Gour Vishwavidyalaya.

## Contents

1. [Overview](#overview)
2. [Features](#features)
3. [Technology stack](#technology-stack)
4. [Project structure](#project-structure)
5. [Requirements](#requirements)
6. [Local installation](#local-installation)
7. [Administrator setup](#administrator-setup)
8. [Run the application](#run-the-application)
9. [Scoring and ranking](#scoring-and-ranking)
10. [Testing](#testing)
11. [Configuration](#configuration)
12. [Deployment on Render](#deployment-on-render)
13. [Data persistence](#data-persistence)
14. [Security considerations](#security-considerations)
15. [Troubleshooting](#troubleshooting)
16. [Limitations and future improvements](#limitations-and-future-improvements)
17. [Credits and copyright](#credits-and-copyright)

## Overview

Code Quiz is designed to provide a simple online quiz experience for Python and related computing subjects. Participants choose a category, difficulty, and quiz length before starting a timed assessment. Answers are evaluated on the server, and results can appear on a leaderboard.

The application includes an administrative area for maintaining the question bank and configuring quiz behaviour. The current project uses JSON files for storage rather than a database.

## Features

| Feature | Description |
|---|---|
| Random question selection | Selects distinct questions from the available question bank. When fewer questions are available than requested, the quiz may be shortened and the participant informed. |
| Timed assessments | Displays a countdown and submits the quiz when time expires. The server validates the deadline rather than trusting the browser timer alone. |
| Negative marking | Supports marks for correct answers and configurable penalties for wrong answers. An unanswered-answer penalty may be enabled where supported by settings. |
| Categories and difficulty | Supports category-based quizzes and easy, medium, hard, or unrestricted difficulty selection. |
| Adjustable quiz length | Lets participants choose the number of questions within configured limits. |
| Results and explanations | Shows score information and, where implemented, correct answers and explanations. |
| Leaderboard | Lists completed quiz results and supports category/difficulty filtering where configured. |
| Question administration | Protected dashboard for adding, editing, searching, categorising, and deleting questions. |
| Quiz settings | Administrative controls for supported quiz length, timing, and scoring options. |
| Input validation | Validates submitted values on the server. |
| Security controls | Includes password hashing, session handling, CSRF protection, and login throttling as implemented by the application. |
| JSON storage | Stores runtime data in JSON files. |
| Responsive interface | Provides a web interface designed for desktop and mobile screens. |
| Automated tests | Includes a pytest test suite. |
| Deployment configuration | Includes configuration files for running with Gunicorn and deploying to Render. |

The optional Tkinter desktop interface is not included; Code Quiz is a web application.

## Technology stack

- **Language:** Python 3.11+
- **Web framework:** Flask
- **Templating:** Jinja2
- **Frontend:** HTML5, CSS3, JavaScript, Bootstrap 5 (CDN)
- **Storage:** JSON files
- **Testing:** pytest
- **Production server:** Gunicorn
- **Hosting configuration:** Render Blueprint

Bootstrap and other assets loaded from a CDN require an internet connection in the browser.

## Project structure

The following is a guide to the intended layout. Confirm filenames against the actual repository if the implementation differs.

```text
Code_Quiz/
├── app.py
├── config.py
├── gunicorn.conf.py
├── render.yaml
├── requirements.txt
├── requirements-dev.txt
├── .env.example
├── .gitignore
├── README.md
├── quiz_app/
│   ├── __init__.py
│   ├── security.py
│   ├── validators.py
│   ├── constants.py
│   ├── routes/
│   │   ├── public.py
│   │   └── admin.py
│   ├── services/
│   │   ├── quiz_service.py
│   │   ├── scoring_service.py
│   │   ├── question_service.py
│   │   ├── settings_service.py
│   │   ├── leaderboard_service.py
│   │   ├── auth_service.py
│   │   └── stats_service.py
│   ├── storage/
│   ├── templates/
│   │   └── admin/
│   └── static/
│       ├── css/
│       │   └── style.css
│       └── js/
│           ├── quiz.js
│           ├── setup.js
│           ├── admin.js
│           └── common.js
├── sample_data/
│   └── questions.json
├── scripts/
│   └── admin_tool.py
├── tests/
└── data/                 # Runtime data; should not be committed
```

## Requirements

Install Python 3.11 or another version supported by the project's dependencies. Check your version with:

```bash
python3 --version
```

You will also need `pip`. Git is optional for local development but useful for version control and deployment.

## Local installation

Run these commands from the project directory:

```bash
cd ~/Desktop/Project/Code_Quiz
python3 -m venv .venv
source .venv/bin/activate
python -m pip install --upgrade pip
pip install -r requirements-dev.txt
```

On Windows, activate the virtual environment with:

```powershell
.venv\Scripts\Activate.ps1
```

Create a local environment file:

```bash
cp .env.example .env
```

On Windows PowerShell:

```powershell
Copy-Item .env.example .env
```

Generate a strong Flask secret key:

```bash
python -c "import secrets; print(secrets.token_urlsafe(48))"
```

Add the generated value to `.env` as `SECRET_KEY`. Use the exact variable names supported by `config.py` and `.env.example`. Never commit `.env` or production secrets.

## Administrator setup

Inspect the available commands before creating an administrator:

```bash
python scripts/admin_tool.py --help
```

If supported by the installed version, create an administrator with:

```bash
python scripts/admin_tool.py create-admin --username admin
```

Alternatively, if the tool supports password-hash generation:

```bash
python scripts/admin_tool.py hash-password
```

Follow the tool's prompts and configuration requirements. Use a strong password and store the resulting hash securely. Do not place a plain-text production password in source code or commit it to Git.

## Run the application

Start the development server:

```bash
python app.py
```

Open the homepage at:

- Local application: <http://127.0.0.1:5000>
- Administrator sign-in: <http://127.0.0.1:5000/admin/login>

The administrator route assumes the route is enabled in the current application configuration. Stop the development server with `Ctrl+C`.

## Using Code Quiz

### Participants

1. Open the homepage.
2. Choose a category and difficulty.
3. Select the desired quiz length.
4. Start the quiz and answer before the timer expires.
5. Submit the quiz or allow automatic submission when time runs out.
6. Review the result and any available answer explanations.
7. Visit the leaderboard to compare results.

### Administrators

1. Open the administrator sign-in page.
2. Sign in using the configured credentials.
3. Use the dashboard to manage questions and supported quiz settings.
4. Review or manage results using the controls available in the application.

## Scoring and ranking

The general scoring formula is:

**Score = (Correct × Marks per correct answer) − (Wrong × Penalty per wrong answer) − (Unanswered × Penalty per unanswered question)**

The unanswered-question penalty is zero when disabled. Depending on the configured rules, a total score may be negative.

**Accuracy = (Correct answers ÷ Total questions) × 100**

The application may scale the allowed duration according to quiz length. The server-side deadline is authoritative; changing the browser clock must not be treated as a valid way to extend a quiz.

Where the leaderboard uses score and accuracy as ranking criteria, participants tied on both values share a rank. Check the current implementation for any additional tie-breakers.

## Testing

Activate the virtual environment and run:

```bash
source .venv/bin/activate
python -m pytest
```

For verbose output:

```bash
python -m pytest -v
```

The project previously reported **174 passing tests**. Run the test suite again after making changes; the latest test output is the source of truth for the current version.

## Configuration

Use `.env.example`, `config.py`, and `gunicorn.conf.py` as the authoritative references for supported settings. Depending on the implementation, configuration may include:

| Variable | Purpose |
|---|---|
| `APP_ENV` | Selects development or production mode. |
| `SECRET_KEY` | Secret used to protect sessions and other signed values. |
| `ADMIN_USERNAME` | Configures the administrator username. |
| `ADMIN_PASSWORD_HASH` | Stores the administrator password hash. |
| `DATA_DIR` | Selects the runtime data directory, if supported. |
| `PORT` | HTTP port supplied by the hosting platform. |
| `SUBMIT_GRACE_SECONDS` | Submission grace period, if supported. |
| `ADMIN_SESSION_MINUTES` | Administrator session duration, if supported. |
| `LOGIN_MAX_ATTEMPTS` | Login-attempt limit, if supported. |
| `LOGIN_LOCK_SECONDS` | Login lockout duration, if supported. |
| `WEB_CONCURRENCY` | Gunicorn worker count, if configured. |
| `GUNICORN_THREADS` | Gunicorn thread count, if configured. |

Do not assume every variable in this table is active in every version. Verify the actual configuration files.

## Deployment on Render

Push the project to GitHub first, then deploy using the Render configuration supplied by the repository.

### Blueprint deployment

1. Sign in to Render.
2. Choose **New → Blueprint**.
3. Connect the GitHub repository containing Code Quiz.
4. Review the detected `render.yaml` settings.
5. Configure required environment variables and secrets.
6. Deploy and inspect the build and runtime logs.

### Manual web service

If the repository's configuration matches the commands below, use:

**Build command**

```bash
pip install -r requirements.txt
```

**Start command**

```bash
gunicorn app:app -c gunicorn.conf.py
```

**Health check path**

```text
/health
```

Use these settings only if they match the current `render.yaml`, application entry point, and health route.

Typical production configuration may require:

```text
APP_ENV=production
SECRET_KEY=<strong-random-secret>
ADMIN_USERNAME=admin
ADMIN_PASSWORD_HASH=<generated-password-hash>
```

Set secrets in Render's environment settings. Do not put real secrets in the README or source repository.

## Data persistence

The application stores runtime information in JSON files. On hosting services with an ephemeral filesystem, runtime changes may be lost when the service restarts or is redeployed. This can affect quiz results, leaderboard entries, administrator-created questions, and settings.

Sample questions may be restored during initialization if the application is designed to seed them, but this does not guarantee recovery of user-created content or results.

For durable production data, migrate to a managed database such as PostgreSQL or use an appropriate persistent-storage option supported by the hosting provider.

## Security considerations

The application is intended to use the following controls where implemented:

- Hashed administrator passwords.
- Session-based authentication.
- CSRF protection for state-changing requests.
- Server-side validation of submitted values.
- Server-side timer and score validation.
- Restricted access to administrative routes.
- Secure session-cookie configuration in production.
- Protection of answer keys from client-side exposure.

Review the implementation and production configuration before relying on these controls in a live environment. Keep dependencies updated and never commit credentials, `.env`, or private user data.

## Troubleshooting

### Virtual environment points to an old path

If `.venv` was copied or the project folder was renamed, recreate it:

```bash
deactivate
rm -rf .venv
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements-dev.txt
```

### Port 5000 is already in use

Stop the previous development server with `Ctrl+C`, or identify the process using the port before starting another instance.

### Administrator login fails

Confirm that the administrator username and password hash match the current configuration. Use the project's administration utility to create or reset credentials where supported. Never share the password or hash publicly.

### Static styles do not update

Hard-refresh the browser with `Ctrl+Shift+R`. If the problem persists, inspect the browser developer tools and verify the CSS file loaded by the template.

### Data is missing after deployment

Check whether the hosting service uses ephemeral storage. JSON data on an ephemeral filesystem is not guaranteed to survive restarts or redeployments.

### Deployment fails

Inspect the Render build and runtime logs. Verify the Python version, dependencies, start command, environment variables, health-check route, and the files referenced by `render.yaml`.

## Limitations and future improvements

Current architectural limitations include JSON-based storage and the persistence constraints of ephemeral hosting. Possible future improvements include:

- PostgreSQL or another database for durable storage.
- Participant accounts and personal result history.
- Exporting results to CSV or PDF.
- Additional categories and question sets.
- Performance analytics and progress tracking.
- Automated backups and recovery.
- Expanded accessibility and security testing.
- A separate Tkinter desktop interface, if required by the assignment.

## Credits and copyright

Developed by **Pritam Rabha** as an independent MCA Python Programming academic project.

**Project Guide:** Dr. Pangambam Sendash Singh  
**Institution:** Dr. Hari Singh Gour Vishwavidyalaya, Sagar, Madhya Pradesh

Copyright © 2026 Pritam Rabha. All rights reserved.

The institution's name is included for academic identification only. This project is not an official university application and does not imply university endorsement.

Third-party libraries and assets remain subject to their respective licences.
