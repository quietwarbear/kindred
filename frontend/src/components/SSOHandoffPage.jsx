import { useEffect, useState } from "react";
import { useNavigate } from "react-router-dom";

import { apiRequest } from "@/lib/api";

// Ubuntu Markets SSO handoff — redeems a one-time code from a sibling product
// (e.g. Ile Ubuntu's "Open in Kindred") and signs the user in. Reached at /sso?code=…
export const SSOHandoffPage = ({ onAuthSuccess }) => {
  const navigate = useNavigate();
  const [error, setError] = useState("");

  useEffect(() => {
    const code = new URLSearchParams(window.location.search).get("code");
    if (!code) {
      setError("Missing sign-in code. Please try again from the other app.");
      return;
    }
    (async () => {
      try {
        const payload = await apiRequest("/auth/sso-redeem", { method: "POST", data: { code } });
        onAuthSuccess(payload);
        navigate("/dashboard", { replace: true });
      } catch (e) {
        setError("This sign-in link has expired or was already used. Please try again.");
      }
    })();
  }, [navigate, onAuthSuccess]);

  return (
    <div className="flex min-h-screen items-center justify-center bg-background px-6 text-center">
      <p className="text-sm text-muted-foreground" data-testid="kindred-sso-status">
        {error || "Signing you in to Kindred…"}
      </p>
    </div>
  );
};

export default SSOHandoffPage;
