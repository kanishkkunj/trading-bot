export type Strategy = {
  id: string;
  name: string;
  description?: string | null;
  version: string;
  is_active: boolean;
  is_default: boolean;
  model_version?: string | null;
  symbols: string[];
};
