FROM python:3.12-slim
WORKDIR /app
COPY source source
COPY public public
COPY data/seed.json data/seed.json
RUN mkdir /store && chown -R 10001:10001 /store /app/data
USER 10001
ENV HOST=0.0.0.0 PORT=3000 CATFACTS_DB=/store/catalog.sqlite3 PYTHONDONTWRITEBYTECODE=1
EXPOSE 3000
CMD ["python", "-m", "source.server"]
