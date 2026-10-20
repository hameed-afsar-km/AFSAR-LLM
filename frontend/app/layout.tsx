import type { Metadata } from "next";
import "./globals.css";

export const metadata: Metadata = {
  title: "AFSAR — Personal AI Assistant",
  description: "AFSAR is a personal AI assistant with voice, memory, and knowledge — built by Afsar.",
};

export default function RootLayout({
  children,
}: Readonly<{
  children: React.ReactNode;
}>) {
  return (
    <html lang="en">
      <head>
        <meta name="viewport" content="width=device-width, initial-scale=1" />
      </head>
      <body>{children}</body>
    </html>
  );
}
