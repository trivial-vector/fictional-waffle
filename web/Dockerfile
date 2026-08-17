# Standalone static-file container for the chat + memory-browser web UI.
# Deliberately decoupled from the `assistant` backend container — this image
# can run on a different host entirely (e.g. the MacBook Air, or any other
# machine) and just needs ASSISTANT_API_BASE_URL / VOICE_SERVICE_URL pointed
# at wherever the backend/voice services actually live (see
# docker-entrypoint.sh and config.js.template).
FROM nginx:alpine

RUN apk add --no-cache gettext  # provides envsubst, used by docker-entrypoint.sh

COPY index.html memory.html config.js.template /usr/share/nginx/html/
COPY static /usr/share/nginx/html/static
COPY nginx.conf /etc/nginx/conf.d/default.conf
COPY docker-entrypoint.sh /docker-entrypoint.sh
RUN chmod +x /docker-entrypoint.sh

EXPOSE 80
ENTRYPOINT ["/docker-entrypoint.sh"]
