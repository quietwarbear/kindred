import { useEffect, useState } from "react";

import { apiRequest } from "@/lib/api";
import { normalizePlans } from "@/lib/pricing";

export const usePublicPlans = () => {
  const [state, setState] = useState({ plans: [], reunionPass: null, loading: true, error: "" });

  useEffect(() => {
    let active = true;
    apiRequest("/subscriptions/plans")
      .then((payload) => {
        if (active) {
          setState({
            plans: normalizePlans(payload?.plans),
            reunionPass: payload?.reunion_pass || null,
            loading: false,
            error: "",
          });
        }
      })
      .catch(() => {
        if (active) {
          setState({
            plans: [],
            reunionPass: null,
            loading: false,
            error: "Current plan details are temporarily unavailable. Please try again shortly.",
          });
        }
      });
    return () => {
      active = false;
    };
  }, []);

  return state;
};
