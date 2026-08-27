import type { Metadata } from "next";
import { Inter } from "next/font/google";
import Script from "next/script";
import "./globals.css";
import { Providers } from "@/components/providers";
import PlatformFeedbackWidget from "@/components/PlatformFeedbackWidget";

const inter = Inter({ subsets: ["latin"], display: "swap" });

export const metadata: Metadata = {
  metadataBase: new URL('https://gapirai.uz'),
  title: {
    default: "GapirAI.uz — YouTube videolarni o'zbek tiliga AI dublyaj qilish",
    template: "%s | GapirAI.uz",
  },
  description: "GapirAI.uz — YouTube videolarni sun'iy intellekt yordamida avtomatik o'zbek tiliga dublyaj qiluvchi onlayn platforma. 45 daqiqagacha videolar bepul.",
  keywords: [
    "gapirai",
    "gapirai uz",
    "gapir ai",
    "gapir ai uz",
    "gapirai.uz",
    "youtube dublyaj",
    "youtube dublaj",
    "video dublyaj",
    "video dublaj",
    "o'zbekcha dublyaj",
    "o'zbek tiliga dublyaj",
    "dublyaj dasturi",
    "dublaj dasturi",
    "dublyaj programmasi",
    "dublaj programmasi",
    "onlayn dublyaj",
    "bepul dublyaj",
    "AI dublyaj",
    "sun'iy intellekt dublyaj",
    "video tarjima",
    "ovozlashtirish",
    "ovoz berish dasturi",
  ],
  authors: [{ name: "GapirAI.uz", url: "https://gapirai.uz" }],
  creator: "GapirAI.uz",
  publisher: "GapirAI.uz",
  alternates: {
    canonical: "/",
  },
  icons: {
    icon: [
      { url: "/icon.png" },
      { url: "/logo.webp", type: "image/webp" },
    ],
    shortcut: ["/favicon.ico"],
    apple: [
      { url: "/apple-icon.png" },
    ],
  },
  openGraph: {
    type: "website",
    locale: "uz_UZ",
    url: "https://gapirai.uz",
    siteName: "GapirAI.uz",
    title: "GapirAI.uz — YouTube videolarni o'zbek tiliga AI dublyaj qilish",
    description: "Sun'iy intellekt yordamida YouTube videolarni avtomatik o'zbek tiliga dublyaj va tarjima qiluvchi onlayn platforma.",
    images: [
      {
        url: "https://gapirai.uz/logo.webp",
        width: 256,
        height: 256,
        alt: "GapirAI.uz logotipi",
      },
    ],
  },
  twitter: {
    card: "summary",
    title: "GapirAI.uz — YouTube videolarni o'zbek tiliga AI dublyaj qilish",
    description: "Videolarni AI yordamida avtomatik o'zbek tiliga dublyaj qiluvchi onlayn platforma.",
    images: ["https://gapirai.uz/logo.webp"],
  },
  robots: {
    index: true,
    follow: true,
    googleBot: {
      index: true,
      follow: true,
      "max-video-preview": -1,
      "max-image-preview": "large",
      "max-snippet": -1,
    },
  },
  verification: {
    google: "srZlb7Q_Zziyn-5bWCG4Kc5NLwyyALavPhPL9MaU_iU",
  },
};

export default function RootLayout({
  children,
}: {
  children: React.ReactNode;
}) {
  const websiteSchema = {
    "@context": "https://schema.org",
    "@type": "WebSite",
    "name": "GapirAI.uz",
    "alternateName": ["GapirAI", "GapirAI uz", "Gapir AI", "Gapir AI uz", "Gapirai dublaj programmasi"],
    "url": "https://gapirai.uz",
    "inLanguage": "uz",
    "description": "YouTube videolarni sun'iy intellekt yordamida avtomatik o'zbek tiliga dublyaj qiluvchi onlayn platforma."
  };

  const organizationSchema = {
    "@context": "https://schema.org",
    "@type": "Organization",
    "name": "GapirAI.uz",
    "url": "https://gapirai.uz",
    "logo": "https://gapirai.uz/logo.webp"
  };

  const softwareAppSchema = {
    "@context": "https://schema.org",
    "@type": "SoftwareApplication",
    "name": "GapirAI.uz",
    "alternateName": ["GapirAI", "GapirAI uz", "Gapir AI", "Gapir AI uz", "Gapirai dublaj programmasi"],
    "applicationCategory": "MultimediaApplication",
    "operatingSystem": "All",
    "url": "https://gapirai.uz",
    "description": "YouTube videolarni sun'iy intellekt yordamida avtomatik o'zbek tiliga dublyaj va tarjima qiluvchi onlayn platforma.",
    "offers": {
      "@type": "Offer",
      "price": "0",
      "priceCurrency": "UZS"
    }
  };

  return (
    <html lang="uz" suppressHydrationWarning>
      <head>
        <script
          type="application/ld+json"
          dangerouslySetInnerHTML={{ __html: JSON.stringify(websiteSchema) }}
        />
        <script
          type="application/ld+json"
          dangerouslySetInnerHTML={{ __html: JSON.stringify(organizationSchema) }}
        />
        <script
          type="application/ld+json"
          dangerouslySetInnerHTML={{ __html: JSON.stringify(softwareAppSchema) }}
        />
      </head>
      <body className={inter.className}>
        <Providers>{children}</Providers>
        <PlatformFeedbackWidget />
        <Script id="yandex-metrika" strategy="afterInteractive">
          {`
            (function(m,e,t,r,i,k,a){
                m[i]=m[i]||function(){(m[i].a=m[i].a||[]).push(arguments)};
                m[i].l=1*new Date();
                for (var j = 0; j < document.scripts.length; j++) {if (document.scripts[j].src === r) { return; }}
                k=e.createElement(t),a=e.getElementsByTagName(t)[0],k.async=1,k.src=r,a.parentNode.insertBefore(k,a)
            })(window, document,'script','https://mc.yandex.ru/metrika/tag.js?id=111361158', 'ym');

            ym(111361158, 'init', {ssr:true, webvisor:true, clickmap:true, ecommerce:"dataLayer", referrer: document.referrer, url: location.href, accurateTrackBounce:true, trackLinks:true});
          `}
        </Script>
        <noscript>
          <div>
            <img src="https://mc.yandex.ru/watch/111361158" style={{ position: "absolute", left: "-9999px" }} alt="" />
          </div>
        </noscript>
      </body>
    </html>
  );
}
