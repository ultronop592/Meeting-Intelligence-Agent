# Deployment Guide: Deploying to Render

This guide describes how to deploy the Meeting Intelligence Agent platform to [Render](https://render.com) using the included `Dockerfile` and `render.yaml` Blueprint.

---

## Option 1: Automated Blueprint Deployment (Recommended)

Render Blueprints let you deploy the entire stack (Backend + Frontend) with a single click.

### Steps:
1. Push your repository to GitHub or GitLab.
2. Log in to the [Render Dashboard](https://dashboard.render.com).
3. Click **New +** in the top navigation and select **Blueprint**.
4. Connect your repository containing `render.yaml`.
5. Render will automatically detect the two services:
   - `meeting-intelligence-backend` (Docker web service)
   - `meeting-intelligence-frontend` (Node web service)
6. Fill in the required environment variables in the Render Blueprint UI:
   - `DATABASE_URL`: Your Neon PostgreSQL connection string (`postgresql+asyncpg://...`)
   - `DATABASE_URL_SYNC`: Your Neon PostgreSQL sync connection string (`postgresql+psycopg2://...`)
   - `GROQ_API_KEY`: Your Groq API key (for Whisper transcription)
   - `OPERNROUTER_API_KEY`: Your OpenRouter API key (for LLM reasoning & agent chat)
   - Optional: `JIRA_URL`, `JIRA_EMAIL`, `JIRA_API_TOKEN`, `SLACK_WEBHOOK_URL`, `SENDGRID_API_KEY`, `SENDER_EMAIL`
7. Click **Apply**. Render will automatically build the container and deploy both services.

---

## Option 2: Deploy Backend Only via Docker

If you only want to deploy the Backend to Render and run the frontend locally or on Vercel:

### Steps:
1. Go to the [Render Dashboard](https://dashboard.render.com).
2. Click **New +** and select **Web Service**.
3. Connect your repository.
4. Configure the service:
   - **Name**: `meeting-intelligence-backend`
   - **Language / Runtime**: `Docker`
   - **Root Directory**: `Backend`
   - **Dockerfile Path**: `Backend/Dockerfile` (or `Dockerfile` if Root Directory is set to `Backend`)
   - **Instance Type**: `Free` or `Starter`
5. Set the Environment Variables under the **Environment** tab:
   - `APP_ENV`: `production`
   - `PORT`: `8000` (Render will map this automatically)
   - `DATABASE_URL`: `postgresql+asyncpg://neondb_owner:...`
   - `DATABASE_URL_SYNC`: `postgresql+psycopg2://neondb_owner:...`
   - `SECRET_KEY`: (Generate a secure random string)
   - `GROQ_API_KEY`: `gsk_...`
   - `OPERNROUTER_API_KEY`: `sk-or-v1-...`
   - `OPENROUTER_MODEL`: `meta-llama/llama-3.3-70b-instruct`
   - `DIARIZATION_ENABLED`: `false` (set to `true` only if you have a paid instance with HF_TOKEN)
   - `CORS_ORIGINS`: `http://localhost:3000,https://your-frontend.vercel.app`
6. Click **Deploy Web Service**.
7. Test the deployment:
   - Open `https://<your-backend-service>.onrender.com/health` in your browser.
   - You should receive: `{"status": "ok", "version": "2.0.0", "database": "neon"}`.

---

## Backend Docker Features

- **Base Image**: `python:3.12-slim` (minimal footprint, fast cold starts).
- **Audio Processing**: Includes `ffmpeg` pre-installed for automatic audio segmentation and chunking.
- **Dynamic Port**: Adapts dynamically to Render's `$PORT` environment variable.
- **Healthcheck**: Built-in container health probe hitting `/health`.
- **Security**: Runs under a dedicated non-root user (`appuser`).
- **CORS Handling**: Automatically permits requests from `*.onrender.com` in production mode and accepts custom domains via `CORS_ORIGINS`.
