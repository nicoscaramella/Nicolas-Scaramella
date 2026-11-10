#!/bin/sh
set -e
# Agrega host.docker.internal con el gateway real de planta-lan (cambia si se
# recrea la red). No falla si no hay ruta.
python -m sistema.hostgw || true
exec "$@"
