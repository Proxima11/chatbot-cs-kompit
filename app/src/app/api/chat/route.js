import { NextResponse } from 'next/server';

export async function POST(req) {
  try {
    const { message } = await req.json();

    // Proxy the request to the Python FastAPI backend
    const backendResponse = await fetch('http://localhost:8000/predict', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ message }),
    });

    if (!backendResponse.ok) {
       console.error(`Python backend returned ${backendResponse.status}`);
       return NextResponse.json({ reply: 'Maaf, model AI sedang tidak dapat diakses saat ini.' }, { status: 500 });
    }

    const data = await backendResponse.json();
    return NextResponse.json({ reply: data.reply });
    
  } catch (error) {
    console.error('Chat API Error:', error);
    return NextResponse.json({ reply: 'Maaf, terjadi kesalahan pada server saat memproses pesan Anda.' }, { status: 500 });
  }
}
