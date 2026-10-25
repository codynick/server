FROM python:3.12-slim
RUN apt-get update && apt-get install -y --no-install-recommends php-cgi php-mysql php-mbstring \
    && rm -rf /var/lib/apt/lists/*
RUN pip install --no-cache-dir pyserial==3.5 requests==2.32.5 keyboard==0.13.5 mysql-connector-python==9.5.0
COPY upstream /upstream
COPY tools/adapt_rpi.py /opt/adapt_rpi.py
RUN python /opt/adapt_rpi.py /upstream /opt/rpi && rm -rf /upstream
COPY runtime/agent.py runtime/call.py runtime/php-prepend.php /opt/agent/
ENV PYTHONPATH=/opt/rpi/client PYTHONUNBUFFERED=1 PYTHONDONTWRITEBYTECODE=1 \
    CODYNICK_LOG_FILE=/home/client/library.log CODYNICK_SIM_TOKEN_FILE=/tmp/sim-token HOME=/home/client
WORKDIR /home/client
USER 10000:10000
CMD ["python", "-u", "/opt/agent/agent.py"]
