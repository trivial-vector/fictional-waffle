#!/bin/sh
# Renders config.js from the environment, then hands off to nginx. The
# explicit variable list passed to envsubst matters: without it, envsubst
# would try to substitute every "$..."-looking token in the template,
# including any that happen to appear elsewhere — restricting it to exactly
# the two variables this template uses avoids that.
set -eu

: "${ASSISTANT_API_BASE_URL:=http://localhost:8081/api}"
: "${VOICE_SERVICE_URL:=http://localhost:8092/transcribe}"
export ASSISTANT_API_BASE_URL VOICE_SERVICE_URL

envsubst '${ASSISTANT_API_BASE_URL} ${VOICE_SERVICE_URL}' \
  < /usr/share/nginx/html/config.js.template \
  > /usr/share/nginx/html/config.js

exec nginx -g "daemon off;"
