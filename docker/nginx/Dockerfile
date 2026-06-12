# Used for production-style builds where nginx.conf is baked into the image.
# For local development, docker-compose mounts nginx.conf directly into the
# stock nginx:alpine image instead (see docker-compose.yml).
FROM nginx:alpine

COPY nginx.conf /etc/nginx/conf.d/default.conf
