import axios from "axios";

export const BACKEND_URL = process.env.REACT_APP_BACKEND_URL;
export const API_URL = `${BACKEND_URL}/api`;

export const apiRequest = async (path, { method = "GET", data, token, params } = {}) => {
  const response = await axios({
    method,
    url: `${API_URL}${path}`,
    data,
    params,
    headers: token
      ? {
          Authorization: `Bearer ${token}`,
        }
      : undefined,
  });

  return response.data;
};

export const convertFileToDataUrl = (file) =>
  new Promise((resolve, reject) => {
    if (!file) {
      resolve("");
      return;
    }

    const reader = new FileReader();
    reader.onload = () => resolve(reader.result?.toString() || "");
    reader.onerror = reject;
    reader.readAsDataURL(file);
  });

export const formatDateTime = (value) => {
  if (!value) return "TBD";
  try {
    return new Date(value).toLocaleString([], {
      dateStyle: "medium",
      timeStyle: "short",
    });
  } catch {
    return value;
  }
};

export const shortCurrency = (value) =>
  new Intl.NumberFormat("en-US", {
    style: "currency",
    currency: "USD",
    maximumFractionDigits: 2,
  }).format(value || 0);