import { lazy, Suspense, type ReactNode } from "react";
import { Navigate, Route, Routes, useLocation } from "react-router";
import { useMe } from "./api/queries";
import { useAuth } from "./auth/AuthContext";
import { CheckYourEmail } from "./components/verify";
import Landing from "./pages/Landing";
import Login from "./pages/Login";
import Register from "./pages/Register";

// The public site ships in the main bundle; the panel and legal pages load on demand,
// so visitors don't download the whole panel.
const Layout = lazy(() => import("./components/Layout"));
const Account = lazy(() => import("./pages/Account"));
const Help = lazy(() => import("./pages/Help"));
const Dashboard = lazy(() => import("./pages/Dashboard"));
const Handoffs = lazy(() => import("./pages/Handoffs"));
const Inbox = lazy(() => import("./pages/Inbox"));
const Instagram = lazy(() => import("./pages/Instagram"));
const InstagramCallback = lazy(() => import("./pages/InstagramCallback"));
const Knowledge = lazy(() => import("./pages/Knowledge"));
const NotFound = lazy(() => import("./pages/NotFound"));
const Playground = lazy(() => import("./pages/Playground"));
const Products = lazy(() => import("./pages/Products"));
const Settings = lazy(() => import("./pages/Settings"));
const Billing = lazy(() => import("./pages/Billing"));
const ForgotPassword = lazy(() => import("./pages/ForgotPassword"));
const ResetPassword = lazy(() => import("./pages/ResetPassword"));
const VerifyEmail = lazy(() => import("./pages/VerifyEmail"));
const Unanswered = lazy(() => import("./pages/Unanswered"));
const Comments = lazy(() => import("./pages/Comments"));
const Stories = lazy(() => import("./pages/Stories"));
const Insights = lazy(() => import("./pages/Insights"));
const Privacy = lazy(() => import("./pages/public/Legal").then((m) => ({ default: m.Privacy })));
const Terms = lazy(() => import("./pages/public/Legal").then((m) => ({ default: m.Terms })));
const DataDeletion = lazy(() => import("./pages/public/Legal").then((m) => ({ default: m.DataDeletion })));

function RequireAuth({ children }: { children: ReactNode }) {
  const { loggedIn } = useAuth();
  const location = useLocation();
  if (!loggedIn) {
    const next = location.pathname + location.search;
    return <Navigate to={`/login${next !== "/" ? `?next=${encodeURIComponent(next)}` : ""}`} replace />;
  }
  return <EmailGate>{children}</EmailGate>;
}

/** The panel opens only after the emailed link is clicked (the API refuses it before that too). */
function EmailGate({ children }: { children: ReactNode }) {
  const { data: me, isPending } = useMe();
  if (isPending) return <div className="min-h-dvh bg-slate-50" />;
  if (me && !me.email_verified_at) return <CheckYourEmail me={me} />;
  return children;
}

function GuestOnly({ children }: { children: ReactNode }) {
  const { loggedIn } = useAuth();
  return loggedIn ? <Navigate to="/" replace /> : children;
}

export default function App() {
  const { loggedIn } = useAuth();
  return (
    <Suspense fallback={<div className="min-h-dvh bg-slate-50" />}>
      <Routes>
        {/* public — Meta's app review needs these without login */}
        <Route path="/privacy" element={<Privacy />} />
        <Route path="/terms" element={<Terms />} />
        <Route path="/data-deletion" element={<DataDeletion />} />

        <Route path="/login" element={<GuestOnly><Login /></GuestOnly>} />
        <Route path="/register" element={<GuestOnly><Register /></GuestOnly>} />
        <Route path="/forgot-password" element={<GuestOnly><ForgotPassword /></GuestOnly>} />
        {/* the emailed link; works logged in or out */}
        <Route path="/reset-password" element={<ResetPassword />} />
        <Route path="/verify-email" element={<VerifyEmail />} />

        {/* "/" is the public site for visitors and the dashboard once logged in */}
        {!loggedIn && <Route index element={<Landing />} />}

        <Route element={<RequireAuth><Layout /></RequireAuth>}>
          {loggedIn && <Route index element={<Dashboard />} />}
          <Route path="handoffs" element={<Handoffs />} />
          <Route path="inbox" element={<Inbox />} />
          <Route path="inbox/:id" element={<Inbox />} />
          <Route path="unanswered" element={<Unanswered />} />
          <Route path="comments" element={<Comments />} />
          <Route path="stories" element={<Stories />} />
          <Route path="insights" element={<Insights />} />
          <Route path="knowledge" element={<Knowledge />} />
          <Route path="products" element={<Products />} />
          <Route path="playground" element={<Playground />} />
          <Route path="settings" element={<Settings />} />
          <Route path="billing" element={<Billing />} />
          <Route path="instagram" element={<Instagram />} />
          <Route path="instagram/callback" element={<InstagramCallback />} />
          <Route path="account" element={<Account />} />
          <Route path="help" element={<Help />} />
          <Route path="*" element={<NotFound />} />
        </Route>
      </Routes>
    </Suspense>
  );
}
