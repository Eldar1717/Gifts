import { describe, expect, it } from "vitest";
import {
  RARITY_META,
  RARITY_ORDER,
  formatCompact,
  formatDate,
  formatNumber,
  formatStars,
  initials,
  pluralize,
  rarityLabel,
  relativeTime,
  splitAmount,
} from "./format";

describe("formatNumber / formatStars", () => {
  it("форматирует числа без потери null", () => {
    expect(formatNumber(1234)).toMatch(/1\s?234/);
    expect(formatNumber(null)).toBe("0");
    expect(formatNumber(undefined)).toBe("0");
  });

  it("добавляет символ Stars", () => {
    expect(formatStars(0)).toBe("0 ★");
    expect(formatStars(2500)).toMatch(/2\s?500 ★/);
  });

  it("сокращает крупные значения", () => {
    expect(formatCompact(999)).toBe("999");
    expect(formatCompact(1500)).toBe("1.5K");
    expect(formatCompact(2000)).toBe("2K");
    expect(formatCompact(3_400_000)).toBe("3.4M");
  });
});

describe("splitAmount", () => {
  it("повторяет серверную формулу комиссии (floor)", () => {
    expect(splitAmount(1000, 10)).toEqual({ commission: 100, seller: 900 });
    expect(splitAmount(333, 15)).toEqual({ commission: 49, seller: 284 });
    expect(splitAmount(99, 10)).toEqual({ commission: 9, seller: 90 });
  });

  it("не теряет и не создаёт Stars при любом проценте", () => {
    for (const amount of [1, 7, 30, 449, 2500]) {
      for (const percent of [0, 5, 10, 20, 33]) {
        const { commission, seller } = splitAmount(amount, percent);
        expect(commission + seller).toBe(amount);
        expect(commission).toBeGreaterThanOrEqual(0);
      }
    }
  });
});

describe("редкости", () => {
  it("содержит все пять уровней в порядке возрастания", () => {
    expect(RARITY_ORDER).toEqual(["common", "uncommon", "rare", "epic", "legendary"]);
    expect(Object.keys(RARITY_META)).toHaveLength(5);
  });

  it("даёт человекочитаемые подписи", () => {
    expect(rarityLabel("legendary")).toBe("Legendary");
    expect(rarityLabel("common")).toBe("Common");
  });
});

describe("даты", () => {
  it("возвращает прочерк для пустых значений", () => {
    expect(formatDate(null)).toBe("—");
    expect(formatDate(undefined, true)).toBe("—");
    expect(relativeTime(null)).toBe("—");
  });

  it("трактует ISO-дату без таймзоны как UTC", () => {
    const iso = "2024-05-01T10:00:00";
    expect(formatDate(iso)).toBe(formatDate(`${iso}Z`));
  });

  it("считает относительное время", () => {
    const now = new Date();
    const fiveMinutesAgo = new Date(now.getTime() - 5 * 60 * 1000).toISOString();
    expect(relativeTime(fiveMinutesAgo)).toBe("5 мин назад");
    expect(relativeTime(new Date(now.getTime() - 30 * 1000).toISOString())).toBe("только что");
  });
});

describe("pluralize / initials", () => {
  it("склоняет по правилам русского языка", () => {
    const forms: [string, string, string] = ["подарок", "подарка", "подарков"];
    expect(pluralize(1, forms)).toBe("подарок");
    expect(pluralize(3, forms)).toBe("подарка");
    expect(pluralize(11, forms)).toBe("подарков");
    expect(pluralize(21, forms)).toBe("подарок");
    expect(pluralize(112, forms)).toBe("подарков");
  });

  it("строит инициалы", () => {
    expect(initials("Иван Петров")).toBe("ИП");
    expect(initials("Ада")).toBe("АД");
    expect(initials("   ")).toBe("GM");
  });
});
