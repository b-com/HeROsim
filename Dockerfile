FROM python:3.12-slim as base

# Setup env
ENV LANG C.UTF-8
ENV LC_ALL C.UTF-8
ENV PYTHONDONTWRITEBYTECODE 1
ENV PYTHONFAULTHANDLER 1

FROM base AS python-deps

# Install pipenv and compilation dependencies
RUN pip install pipenv
RUN apt-get update && apt-get install -y --no-install-recommends gcc

# Install python dependencies in /.venv
COPY Pipfile .
COPY Pipfile.lock .
RUN PIPENV_VENV_IN_PROJECT=1 pipenv install --deploy

FROM base AS runtime

# Create new user
RUN useradd --create-home app

# Copy virtual env from python-deps stage
COPY --from=python-deps --chown=app:app /.venv /.venv
ENV PATH="/.venv/bin:$PATH"

# Disable entrypoint script development environment check
ENV PIPENV_ACTIVE=1

# Switch to new user
USER app
WORKDIR /home/app

# Persistent volumes for output files
RUN mkdir /home/app/chart
RUN mkdir /home/app/log
RUN mkdir /home/app/result
VOLUME /home/app/chart
VOLUME /home/app/log
VOLUME /home/app/result

# Install application into container
COPY --chown=app:app . .

# Run the scenario
# ENTRYPOINT ["python", "-m", "src.placement"]
# CMD ["--clear", "-i", "data/ids/infrastructure.json", "-d", "data/ids", "-w", "data/ids/traces/workload-83-600.json", "-s", "hrc_hrc", "-c", "fifo", "-t", "least_penalty", "-k", "30", "-q", "100"]
ENTRYPOINT ["bash"]
CMD ["./scenario-ids.sh"]
