FROM python:3.12-slim

WORKDIR /app

COPY pivo /app/pivo

ENV PYTHONUNBUFFERED=1

EXPOSE 8088

ENTRYPOINT ["python", "-m", "pivo.hub_server"]
