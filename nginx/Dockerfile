# Image ringan nginx berbasis Alpine untuk VPS kecil
FROM nginx:1.27-alpine

# Hapus default config
RUN rm /etc/nginx/conf.d/default.conf

# Salin config kustom kita
COPY nginx.conf /etc/nginx/conf.d/app.conf

# Expose port HTTP
EXPOSE 80

# Jalankan nginx di foreground (penting untuk Docker)
CMD ["nginx", "-g", "daemon off;"]
