FROM python:3.13-slim
ENV PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 \
    OMP_NUM_THREADS=1 OPENBLAS_NUM_THREADS=1 MKL_NUM_THREADS=1 \
    BANKBOT_DEPLOYMENT=cloud BANKBOT_DB_PATH=/data/portal.sqlite3
WORKDIR /app
COPY requirements-web.lock.txt /app/
RUN python -m pip install --no-cache-dir -r requirements-web.lock.txt
COPY bankbot/ /app/bankbot/
COPY web/ /app/web/
COPY data/ /app/data/
RUN mkdir -p /data
EXPOSE 8080
CMD ["python", "-m", "bankbot.cloud"]
