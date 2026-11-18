import type { Metadata } from "next";
import Link from "next/link";
import "./globals.css";

export const metadata: Metadata = {
  title: "Radar de precios",
  description: "Precios de supermercados chilenos: historial, mínimos de 90 días y alertas de caída.",
};

export default function RootLayout({ children }: { children: React.ReactNode }) {
  return (
    <html lang="es-CL">
      <body>
        <header className="top">
          <div className="container">
            <Link href="/" className="logo">
              Radar<span>.</span>precios
            </Link>
            <nav>
              <Link href="/">Inicio</Link>
              <Link href="/productos">Productos</Link>
            </nav>
          </div>
        </header>
        <main className="container">{children}</main>
        <footer>
          <div className="container">
            Proyecto de portafolio. Datos de demostración generados por una fuente simulada determinista.
          </div>
        </footer>
      </body>
    </html>
  );
}
