import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "Asistente Offline",
  description: "Asistente de voz personal, 100% offline",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="es">
      <body>{children}</body>
    </html>
  );
}
