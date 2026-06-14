FROM nginx:1.27-alpine

COPY studio/frontend/nginx.conf /etc/nginx/conf.d/default.conf
COPY studio/frontend/index.html /usr/share/nginx/html/index.html
COPY studio/frontend/styles.css /usr/share/nginx/html/styles.css
COPY studio/frontend/app.js /usr/share/nginx/html/app.js
COPY docs/HOWTO-VPN.md /usr/share/nginx/html/HOWTO-VPN.md

EXPOSE 80
