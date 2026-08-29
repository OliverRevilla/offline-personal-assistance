/** @type {import('next').NextConfig} */
const nextConfig = {
  // Tauri sirve la app como archivos estáticos desde su webview, no hay servidor Node en
  // runtime — ver docs/adr/0008-frontend-nativo-windows-y-stack-tauri.md.
  output: "export",
  images: {
    unoptimized: true, // la optimización de next/image necesita un servidor, no disponible en export estático
  },
};

export default nextConfig;
