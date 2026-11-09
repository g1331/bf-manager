import catalog from "../../../backend/app/domain/games/bf6/catalog.json";
import type { Bf6CatalogItem, Bf6MapInfo, Bf6ModeInfo } from "./catalog";

export const WEAPONS: Record<string, Bf6CatalogItem> = catalog.weapons;
export const VEHICLES: Record<string, Bf6CatalogItem> = catalog.vehicles;
export const GADGETS: Record<string, Bf6CatalogItem> = catalog.gadgets;
export const MAPS: Record<string, Bf6MapInfo> = catalog.maps;
export const MODES: Record<string, Bf6ModeInfo> = catalog.modes;
export const WEAPON_CATEGORIES = catalog.weapon_categories;
export const VEHICLE_CATEGORIES = catalog.vehicle_categories;
export const KITS: Record<string, { zh: string; en: string }> = catalog.kits;
export const VEHICLE_TYPES: Record<string, string> = catalog.vehicle_types;
