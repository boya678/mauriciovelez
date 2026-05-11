export interface SuperadminUser {
  id: string;
  email: string;
  name: string;
  active: boolean;
  created_at: string;
}

export interface SuperadminTokenOut {
  access_token: string;
  token_type: string;
}
