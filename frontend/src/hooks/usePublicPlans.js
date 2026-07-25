import { useEffect, useState } from "react";

import { apiRequest } from "@/lib/api";
import { normalizePlans } from "@/lib/pricing";

export const usePublicPlans = () => {
  const [state, setState] = useState({ plans: [], loading: true, error: "" });

  useEffect(() => {
    let active = true;
    apiRequest("/subscriptions/plans")
      .then((payload) => {
        if (active) setState({ plans: normalizePlans(payload?.plans), loading: false, error: "" });
      })
      .catch(() => {
        if (active) {
          setState({
            plans: [],
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
