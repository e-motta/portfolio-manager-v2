import { useSearchParams } from "react-router-dom";

export function useFinancePeriod() {
  const [params] = useSearchParams();
  const year = params.get("year") ? Number(params.get("year")) : new Date().getFullYear();
  const month = params.has("month") ? Number(params.get("month")) : null;
  const query = `year=${year}${month ? `&month=${month}` : ""}`;
  return { year, month, query };
}
