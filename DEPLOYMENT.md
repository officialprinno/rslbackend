# Railway + Neon PostgreSQL Deployment Checklist

Use this after configuring Railway variables and connecting the Neon database.

## Pre-deploy (local)

- [ ] Copy `.env.example` to `.env` and set `DATABASE_URL` (Neon connection string with `?sslmode=require`)
- [ ] `pip install -r requirements.txt`
- [ ] `python manage.py check`
- [ ] `python manage.py check --deploy --settings=config.settings.production` (with production env vars exported)
- [ ] `python manage.py migrate --plan`
- [ ] `python manage.py migrate`
- [ ] `python manage.py collectstatic --noinput --settings=config.settings.production`
- [ ] Confirm `.env` is **not** tracked: `git status` should not list `.env`

## Railway service configuration

- [ ] Root directory set to `backend` (if monorepo)
- [ ] `DJANGO_SETTINGS_MODULE=config.settings.production`
- [ ] All variables from the table below are set in Railway
- [ ] Health check path: `/health/`
- [ ] Release command runs migrations + collectstatic (see `railway.toml` / `Procfile`)

## Post-deploy verification

| Check | Command / URL | Expected |
|-------|----------------|----------|
| Django starts | Railway Deploy Logs | No `ImproperlyConfigured` or import errors |
| Gunicorn starts | Railway Deploy Logs | `Listening at: http://0.0.0.0:<PORT>` |
| Health endpoint | `GET https://<service>.up.railway.app/health/` | HTTP **200**, `{"status":"ok",...}` |
| Database connection | `python manage.py migrate` in release logs | `Applying ... OK` or `No migrations to apply` |
| Admin panel | `https://<service>.up.railway.app/admin/` | Login page loads, CSS/JS present |
| Static files | Admin page styles, `/static/admin/css/base.css` | HTTP **200** (WhiteNoise) |
| API | `https://<service>.up.railway.app/api/v1/` | Responds (auth may return 401) |

## Railway environment variables

| Variable | Example value | Required |
|----------|---------------|----------|
| `SECRET_KEY` | `<django-secret-key>` | Yes |
| `DEBUG` | `False` | Yes |
| `DJANGO_SETTINGS_MODULE` | `config.settings.production` | Yes |
| `DATABASE_URL` | `<NEON_DATABASE_URL>` | Yes |
| `DJANGO_ALLOWED_HOSTS` | `.up.railway.app` | Yes |
| `CSRF_TRUSTED_ORIGINS` | `https://<railway-domain>.up.railway.app` | Yes |
| `CORS_ALLOWED_ORIGINS` | `https://<frontend-domain>` | Yes |
| `FRONTEND_URL` | `https://<frontend-domain>` | Optional (Jazzmin admin link) |

Railway auto-injects `RAILWAY_PUBLIC_DOMAIN` and `PORT` — do not set `PORT` manually.

## Troubleshooting

- **502 / app crash on boot**: Check Deploy Logs for missing `SECRET_KEY`, `DATABASE_URL`, or `CORS_ALLOWED_ORIGINS`.
- **400 Bad Request (DisallowedHost)**: Add your Railway domain to `DJANGO_ALLOWED_HOSTS` or use `.up.railway.app`.
- **CSRF failures on admin**: Ensure `CSRF_TRUSTED_ORIGINS` uses `https://` and matches the public URL.
- **Static files 404**: Confirm release command ran `collectstatic` and `whitenoise` is in `MIDDLEWARE`.
- **Database SSL errors (Neon)**: Use pooled Neon URL with `?sslmode=require` in `DATABASE_URL`.
