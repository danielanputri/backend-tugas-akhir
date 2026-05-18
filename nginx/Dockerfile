FROM nginx:alpine

# Hapus konfigurasi default nginx
RUN rm /etc/nginx/conf.d/default.conf

# Salin konfigurasi reverse proxy
COPY nginx.conf /etc/nginx/conf.d/

EXPOSE 80

CMD ["nginx", "-g", "daemon off;"]
