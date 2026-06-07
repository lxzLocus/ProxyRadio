FROM nginx:alpine

# nginx 設定
COPY nginx.conf /etc/nginx/conf.d/default.conf

# 静的ファイル
COPY index.html /usr/share/nginx/html/
COPY style.css  /usr/share/nginx/html/
COPY app.js     /usr/share/nginx/html/

# env-config.js 生成スクリプト
COPY docker-entrypoint.sh /docker-entrypoint.sh
RUN chmod +x /docker-entrypoint.sh

# デフォルトの env-config.js（開発用）
RUN echo 'window.__RADIKO_BACKEND_URL = "";' > /usr/share/nginx/html/env-config.js

EXPOSE 80

ENTRYPOINT ["/docker-entrypoint.sh"]
CMD ["nginx", "-g", "daemon off;"]
