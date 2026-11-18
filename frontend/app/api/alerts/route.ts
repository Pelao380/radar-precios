import { API_URL } from "@/lib/api";

export async function POST(req: Request) {
  const body = await req.text();
  const res = await fetch(`${API_URL}/alerts`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body,
    cache: "no-store",
  });
  return new Response(await res.text(), { status: res.status, headers: { "Content-Type": "application/json" } });
}
