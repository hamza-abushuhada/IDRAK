export type ProductRow = {
  id: string; sku: string | null; barcode: string | null; name: string; name_ar: string | null; brand: string | null; size: string | null;
  cost: number; price: number; tax_rate: number; reorder_level: number; is_perishable: boolean; category_id: string | null; category: string | null; category_ar: string | null;
  supplier: string | null; supplier_ar: string | null; stock: number; stock_known?: boolean; sold30: number; revenue30: number; profit30: number;
  next_expiry: string | null; margin: number | null;
};

export const daysUntil = (d: string | null) => (d ? Math.ceil((new Date(d).getTime() - Date.now()) / 86400000) : null);

// A cost more than 3x the selling price is almost always a data error (fils read
// as dinars, a carton cost on a single unit), not a real loss: show "check the
// cost" instead of a margin like -41438%.
export const SUSPECT_COST_RATIO = 3;

// Same rules as the "filter" in api/app/routers/workspace.py (products).
export function productFlags(p: ProductRow) {
  const exp = daysUntil(p.next_expiry);
  const belowCost = p.price > 0 && p.cost > p.price;
  return {
    // A product with no selling price (a raw material) isn't sold below cost.
    belowCost,
    suspectCost: belowCost && p.cost > p.price * SUSPECT_COST_RATIO,
    // No stock record at all means stock isn't tracked, not that it's out.
    lowStock: p.stock_known !== false && p.stock <= p.reorder_level,
    dead: p.stock > 0 && p.sold30 <= 0.5,
    expiring: exp !== null && exp <= 14,
    expDays: exp,
  };
}

