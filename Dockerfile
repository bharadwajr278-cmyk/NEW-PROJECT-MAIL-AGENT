FROM python:3.13-slim

WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY monitor.py admin.py ./
COPY templates ./templates
COPY static ./static
RUN mkdir -p /app/data && useradd --system --uid 10001 monitor && chown -R monitor:monitor /app
USER monitor
CMD ["python", "-u", "monitor.py"]
