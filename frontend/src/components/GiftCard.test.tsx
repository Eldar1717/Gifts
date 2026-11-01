import { describe, expect, it } from "vitest";
import { render, screen } from "@testing-library/react";
import { MemoryRouter } from "react-router-dom";
import { MarketGiftCard } from "./GiftCard";
import type { MarketCard } from "../lib/types";

const item = {
  id: 3,
  name: "Violet Heart",
  image_url: "/gifts/crystal-heart.jpg",
  back_image_url: "/gifts/crystal-heart.jpg",
  rarity: "epic" as const,
  glow: "#a855f7",
  primary_price_stars: 780,
  edition_size: 80,
  minted_count: 5,
  remaining: 75,
  status: "active" as const,
  source: "internal" as const,
  is_tradeable: true,
  is_featured: true,
  collection: {
    id: 2,
    slug: "crystal-hearts",
    name: "Кристальные Сердца",
    rarity: "epic" as const,
    cover_url: "/gifts/crystal-heart.jpg",
    accent: "#a855f7",
  },
  created_at: "2026-10-02T12:49:09",
};

const base: MarketCard = {
  kind: "resale",
  key: "listing-7",
  item,
  listing_id: 7,
  ownership_id: 17,
  price_stars: 1390,
  seller: {
    id: 6,
    username: "atlas_shop",
    display_name: "Атлас Громов",
    photo_url: "",
    rating: 5,
  },
  serial_number: 5,
  listed_at: "2026-11-01T06:49:09",
  views: 161,
};

function renderCard(card: MarketCard) {
  return render(
    <MemoryRouter>
      <MarketGiftCard card={card} />
    </MemoryRouter>,
  );
}

describe("MarketGiftCard", () => {
  it("ведёт на страницу лота при перепродаже", () => {
    renderCard(base);
    const link = screen.getByRole("link");
    expect(link.getAttribute("href")).toBe("/listing/7");
    expect(screen.getByText("Violet Heart")).toBeTruthy();
    expect(screen.getByText("Кристальные Сердца")).toBeTruthy();
    expect(screen.getByText("#5")).toBeTruthy();
    expect(screen.getByText("Атлас")).toBeTruthy();
  });

  it("ведёт на карточку предмета для первичного выпуска", () => {
    renderCard({
      ...base,
      kind: "primary",
      key: "item-3",
      listing_id: null,
      ownership_id: null,
      price_stars: item.primary_price_stars,
      seller: null,
      serial_number: null,
    });
    expect(screen.getByRole("link").getAttribute("href")).toBe("/gift/3");
    expect(screen.getByText("75 осталось")).toBeTruthy();
  });

  it("показывает цену именно лота, а не первичную", () => {
    renderCard(base);
    // 1390 (цена лота) отформатирована с разделителем тысяч
    expect(screen.getByText(/1\s?390/)).toBeTruthy();
    expect(screen.queryByText(/^780$/)).toBeNull();
  });
});
