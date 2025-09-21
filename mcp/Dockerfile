# Use an official, slim Python image for a smaller footprint.
FROM python:3.9-slim

# Set the working directory inside the container.
WORKDIR /app

# Copy requirements and install dependencies first to leverage Docker's build cache.
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy the application code into the container.
COPY . .

# Expose the port the app will run on.
EXPOSE 8080

# Use a production-grade WSGI server (Gunicorn) to run the Flask app.
CMD ["gunicorn", "--bind", "0.0.0.0:8080", "--workers", "2", "app:app"]