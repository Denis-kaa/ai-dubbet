import { MetadataRoute } from 'next'

export default function robots(): MetadataRoute.Robots {
  return {
    rules: [
      {
        userAgent: '*',
        allow: '/',
        // Only block the API. /dashboard and /video are handled with a noindex
        // meta tag instead — blocking them here would stop Google from ever
        // crawling the page to see that tag.
        disallow: ['/api/'],
      },
    ],
    sitemap: 'https://gapirai.uz/sitemap.xml',
    host: 'https://gapirai.uz',
  }
}
