const LOCAL_HOSTS = new Set(["localhost", "127.0.0.1"]);

/**
 * Базовый URL API.
 *
 * По умолчанию — same-origin (""), т.е. все запросы идут относительными
 * путями (/api/...) на тот же хост, откуда загружен фронтенд. nginx на
 * сервере проксирует /api/* -> backend :8000, поэтому это работает и по
 * IP (http://185.233.184.192), и через домен (http(s)://gapirai.uz),
 * без CORS и без жёстко зашитого https://api.gapirai.uz (который не
 * резолвился и ломал логин при заходе по IP).
 *
 * NEXT_PUBLIC_API_URL можно задать для явного указания внешнего API
 * (например, отдельный api-домен в будущем).
 */
export function getApiUrl(): string {
  if (process.env.NEXT_PUBLIC_API_URL) {
    return process.env.NEXT_PUBLIC_API_URL;
  }

  if (typeof window !== "undefined" && LOCAL_HOSTS.has(window.location.hostname)) {
    return "http://localhost:8000";
  }

  return "";
}
