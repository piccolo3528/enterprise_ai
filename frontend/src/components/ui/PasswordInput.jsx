import { Eye, EyeOff } from "lucide-react";
import { useState } from "react";

import Input from "./Input";

/** A password field with a show/hide button, so people can check what they typed. */
export default function PasswordInput(props) {
  const [visible, setVisible] = useState(false);
  const Icon = visible ? EyeOff : Eye;

  return (
    <Input
      {...props}
      type={visible ? "text" : "password"}
      trailing={
        <button
          type="button"
          onClick={() => setVisible((v) => !v)}
          aria-label={visible ? "Hide password" : "Show password"}
          aria-pressed={visible}
          className="rounded p-1 text-slate-400 hover:text-slate-600"
        >
          <Icon aria-hidden="true" className="size-4" />
        </button>
      }
    />
  );
}
