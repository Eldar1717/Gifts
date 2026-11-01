import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { ApiError, api, errorMessage, setDevTelegramId } from "./api";

type FetchCall = { url: string; init: RequestInit };

const calls: FetchCall[] = [];

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

beforeEach(() => {
  calls.length = 0;
  vi.stubGlobal(
    "fetch",
    vi.fn(async (url: string, init: RequestInit = {}) => {
      calls.push({ url, init });
      return jsonResponse({ ok: true });
    }),
  );
  localStorage.clear();
});

afterEach(() => {
  vi.unstubAllGlobals();
});

describe("api: запросы", () => {
  it("строит query-строку, пропуская пустые значения", async () => {
    await api.market({ page: 2, q: "drake", rarity: ["rare", "epic"], min: undefined, max: null, featured: true });
    const { url } = calls[0];
    expect(url.startsWith("/api/market?")).toBe(true);
    const params = new URLSearchParams(url.split("?")[1]);
    expect(params.get("page")).toBe("2");
    expect(params.get("q")).toBe("drake");
    expect(params.getAll("rarity")).toEqual(["rare", "epic"]);
    expect(params.has("min")).toBe(false);
    expect(params.has("max")).toBe(false);
    expect(params.get("featured")).toBe("true");
  });

  it("отправляет dev-заголовок только при явной настройке", async () => {
    await api.meta();
    expect(new Headers(calls[0].init.headers).has("X-Dev-Telegram-Id")).toBe(false);

    setDevTelegramId("900000001");
    await api.meta();
    expect(new Headers(calls[1].init.headers).get("X-Dev-Telegram-Id")).toBe("900000001");

    setDevTelegramId(null);
    await api.meta();
    expect(new Headers(calls[2].init.headers).has("X-Dev-Telegram-Id")).toBe(false);
  });

  it("создаёт заказ только по идентификатору предмета/лота — без цены с клиента", async () => {
    await api.invoice({ listing_id: 12 });
    const body = JSON.parse(String(calls[0].init.body));
    expect(body).toEqual({ listing_id: 12 });
    expect(Object.keys(body)).toHaveLength(1);
    expect(calls[0].init.method).toBe("POST");
  });

  it("кодирует slug коллекции в пути", async () => {
    await api.collection("aurum court");
    expect(calls[0].url).toBe("/api/collections/aurum%20court");
  });

  it("возвращает undefined для 204", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response(null, { status: 204 })));
    await expect(api.cancelListing(5)).resolves.toBeUndefined();
  });
});

describe("api: ошибки", () => {
  it("переводит 409 с detail в ApiError", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => jsonResponse({ detail: "Лот уже продан" }, 409)));
    await expect(api.createListing({ ownership_id: 1, price_stars: 100 })).rejects.toMatchObject({
      status: 409,
      detail: "Лот уже продан",
    });
  });

  it("сворачивает ошибки валидации Pydantic в читаемый текст", async () => {
    vi.stubGlobal(
      "fetch",
      vi.fn(async () =>
        jsonResponse(
          { detail: [{ loc: ["body", "price_stars"], msg: "must be greater than 0" }] },
          422,
        ),
      ),
    );
    const error = await api.createListing({ ownership_id: 1, price_stars: 0 }).catch((e) => e);
    expect(error).toBeInstanceOf(ApiError);
    expect(error.detail).toBe("price_stars: must be greater than 0");
  });

  it("подменяет текст для 429 и 5xx", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => jsonResponse({ detail: "raw" }, 429)));
    const tooMany = await api.home().catch((e) => e);
    expect(tooMany.detail).toMatch(/Слишком много запросов/);

    vi.stubGlobal("fetch", vi.fn(async () => new Response("boom", { status: 502 })));
    const server = await api.home().catch((e) => e);
    expect(server.status).toBe(502);
    expect(server.detail).toMatch(/Сервер временно недоступен/);
  });

  it("сообщает об отсутствии соединения", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => Promise.reject(new TypeError("Failed to fetch"))));
    const error = await api.home().catch((e) => e);
    expect(error.status).toBe(0);
    expect(error.detail).toMatch(/Нет соединения/);
  });

  it("пробрасывает признак auth_required", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => jsonResponse({ detail: "Нужна авторизация", auth_required: true }, 401)));
    const error = await api.me().catch((e) => e);
    expect(error.authRequired).toBe(true);
    expect(errorMessage(error)).toBe("Нужна авторизация");
  });

  it("не падает на не-JSON ответе", async () => {
    vi.stubGlobal("fetch", vi.fn(async () => new Response("<html>bad gateway</html>", { status: 500 })));
    const error = await api.home().catch((e) => e);
    expect(error.status).toBe(500);
    expect(errorMessage(error)).toMatch(/Сервер временно недоступен/);
  });
});
