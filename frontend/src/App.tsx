import { Link, Route, Routes } from "react-router-dom";
import AuctionList from "./pages/AuctionList";
import AuctionDetail from "./pages/AuctionDetail";
import CreateRFQ from "./pages/CreateRFQ";

export default function App() {
  return (
    <div className="min-h-screen">
      <header className="bg-slate-900 text-white px-6 py-3 flex items-center gap-6">
        <Link to="/" className="font-semibold text-lg">British Auction RFQ</Link>
        <Link to="/create" className="text-sm opacity-80 hover:opacity-100">+ New RFQ</Link>
      </header>
      <main className="max-w-6xl mx-auto p-6">
        <Routes>
          <Route path="/" element={<AuctionList />} />
          <Route path="/create" element={<CreateRFQ />} />
          <Route path="/rfqs/:id" element={<AuctionDetail />} />
        </Routes>
      </main>
    </div>
  );
}