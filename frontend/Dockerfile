FROM nginx:stable-alpine
COPY frontend/index.html /usr/share/nginx/html/index.html
COPY frontend/fuji-wallet.html /usr/share/nginx/html/fuji-wallet.html
COPY frontend/assets /usr/share/nginx/html/assets
COPY frontend/src /usr/share/nginx/html/src
COPY frontend/nginx.conf.template /etc/nginx/templates/default.conf.template
ENV BACKEND_URL=http://backend:10000
EXPOSE 80
