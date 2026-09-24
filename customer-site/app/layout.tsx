import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "BlackMarket Tunisie — Services digitaux en DT",
  description: "Choisis ton service digital, paie avec D17 ou Flouci et fais vérifier ton paiement simplement sur WhatsApp.",
  icons: {
    icon: "/favicon.svg",
    shortcut: "/favicon.svg",
  },
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="fr">
      <body className="antialiased">{children}</body>
    </html>
  );
}
