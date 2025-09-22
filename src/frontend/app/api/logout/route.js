// app/api/logout/route.js
export function POST() {
  return new Response(null, {
    status: 204,
    headers: {
      'Set-Cookie': 'boa_id_token=; Path=/; HttpOnly; SameSite=Lax; Max-Age=0',
    },
  });
}
