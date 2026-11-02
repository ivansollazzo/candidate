# pg_dump and psql of the same major version as the database (postgres:17 in docker-compose.yml)
FROM postgres:17-alpine
RUN apk add --no-cache python3 tzdata
COPY backup.py /backup.py
EXPOSE 8080
ENTRYPOINT ["python3", "-u", "/backup.py"]
