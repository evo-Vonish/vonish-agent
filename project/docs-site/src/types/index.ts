export interface NavItem {
  id: string;
  label: string;
  href: string;
  children?: NavItem[];
}

export interface DocSection {
  id: string;
  title: string;
  content: string;
}

export interface DocData {
  [key: string]: DocSection;
}
