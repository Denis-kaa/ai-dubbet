"use client";

import { ThemeProvider } from "next-themes";

// mounted guardi olib tashlandi — ThemeProvider har doim ishlaydi.
// html elementi suppressHydrationWarning orqali hydration xatolarini bostiradi.
export function Providers({ children }: { children: React.ReactNode }) {
  return (
    <ThemeProvider attribute="class" defaultTheme="light" enableSystem={false}>
      {children}
    </ThemeProvider>
  );
}
