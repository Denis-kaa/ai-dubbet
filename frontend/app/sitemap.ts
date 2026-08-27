import { MetadataRoute } from 'next'

const baseUrl = 'https://gapirai.uz'

// Static build timestamp. Using `new Date()` here would stamp every URL with the
// build time on each deploy, which trains Google to distrust <lastmod>.
const lastModified = new Date('2026-08-05')

export default function sitemap(): MetadataRoute.Sitemap {
  return [
    { url: baseUrl, lastModified, changeFrequency: 'weekly', priority: 1.0 },
    { url: `${baseUrl}/about`, lastModified, changeFrequency: 'monthly', priority: 0.8 },
    { url: `${baseUrl}/faq`, lastModified, changeFrequency: 'monthly', priority: 0.8 },
    { url: `${baseUrl}/pricing`, lastModified, changeFrequency: 'monthly', priority: 0.8 },
    { url: `${baseUrl}/library`, lastModified, changeFrequency: 'weekly', priority: 0.6 },
    { url: `${baseUrl}/terms`, lastModified, changeFrequency: 'yearly', priority: 0.3 },
    { url: `${baseUrl}/privacy`, lastModified, changeFrequency: 'yearly', priority: 0.3 },
  ]
}
