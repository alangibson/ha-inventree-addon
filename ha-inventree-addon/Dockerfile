ARG BUILD_FROM=inventree/inventree:1.6.4
FROM ${BUILD_FROM}

USER root
# InvenTree resolves its expected Docker data path before validating config
# locations. Alias it to our private directory in Home Assistant's /data mount.
RUN ln -s /data/ha-inventree-addon /home/inventree/data

RUN apt-get update \
    && apt-get install -y --no-install-recommends nginx \
    && rm -rf /var/lib/apt/lists/*

COPY requirements-plugins.txt /opt/ha-inventree/requirements-plugins.txt
RUN python3 -m pip install --no-cache-dir --require-hashes \
    -r /opt/ha-inventree/requirements-plugins.txt

# Smart Parts writes its activity log beside the installed package. Keep it
# on the persistent volume when this image is replaced.
RUN python3 -c "import importlib.util; from pathlib import Path; package = Path(importlib.util.find_spec('inventree_smart_parts').origin).parent; (package / 'smart_parts_activity.jsonl').symlink_to('/data/ha-inventree-addon/smart_parts_activity.jsonl')"

COPY nginx.conf /etc/nginx/nginx.conf
COPY run.py /opt/ha-inventree/run.py
COPY addon_settings.py /opt/ha-inventree/addon_settings.py
WORKDIR /home/inventree
EXPOSE 8080
STOPSIGNAL SIGTERM
ENTRYPOINT ["python3", "/opt/ha-inventree/run.py"]
CMD []
