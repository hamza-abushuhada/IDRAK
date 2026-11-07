export type ProductRow = {
  id: string; sku: string | null; barcode: string | null; name: string; name_ar: string | null; brand: string | null; size: string | null;
  cost: number; price: number; tax_rate: number; reorder_level: number; is_perishable: boolean; category_id: string | null; category: string | null; category_ar: string | null;
  supplier: string | null; supplier_ar: string | null; stock: number; sold30: number; revenue30: number; profit30: number; next_expiry: string | null; margin: number | null;
};

export const daysUntil = (d: string | null) => (d ? Math.ceil((new Date(d).getTime() - Date.now()) / 86400000) : null);

export function productFlags(p: ProductRow) {
  const exp = daysUntil(p.next_expiry);
  return {
    belowCost: p.cost > p.price,
    lowStock: p.stock <= p.reorder_level,
    dead: p.stock > 0 && p.sold30 <= 0.5,
    expiring: exp !== null && exp <= 14,
    expDays: exp,
  };
}

