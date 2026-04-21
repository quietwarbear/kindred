import axios from "axios";

export const BACKEND_URL = process.env.REACT_APP_BACKEND_URL || "https://kindred.ubuntumarket.com";
export const API_URL = `${BACKEND_URL}/api`;

export const apiRequest = async (path, { method = "GET", data, token, params, timeout = 15000 } = {}) => {
  const response = await axios({
    method,
    url: `${API_URL}${path}`,
    data,
    params,
    timeout,
    withCredentials: true,
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

export const formatCountdown = (days) => {
  if (days === null || days === undefined) return "TBD";
  if (days < 0) return "Started";
  if (days === 0) return "Today";
  if (days === 1) return "1 day";
  return `${days} days`;
};

export const formatDateInputValue = (value) => {
  if (!value) return "";
  const date = new Date(value);
  if (Number.isNaN(date.getTime())) return "";
  const pad = (input) => `${input}`.padStart(2, "0");
  return `${date.getFullYear()}-${pad(date.getMonth() + 1)}-${pad(date.getDate())}T${pad(date.getHours())}:${pad(date.getMinutes())}`;
};