-- Ported from psred (github.com/WulfKolbe/psred), playground/featjudge/featjudge/texroles.lua at origin/master 56cf8f6.
-- texroles.lua: give every math char an id, record its role from TeX's noad
-- tree, colour each resulting glyph with its id (pdf_literal whatsits inserted
-- AFTER mlist_to_hlist: zero size, so the layout cannot change - and
-- texroles.py checks that against an uncoloured run).
local ATTR = 4711
local roles, nextid = {}, 0
local MCHAR, SUBML = node.id("math_char"), node.id("sub_mlist")
local NOAD, FRAC, RAD, ACC = node.id("noad"), node.id("fraction"), node.id("radical"), node.id("accent")
local STYLE = node.id("style")
local SUBBOX, GLYPH0, HL0, VL0 = node.id("sub_box"), node.id("glyph"), node.id("hlist"), node.id("vlist")

-- full Appendix G styles: D D' T T' S S' SS SS' (fs); `style` (old field) = its size name
local FS = {display="D", crampeddisplay="D'", text="T", crampedtext="T'", script="S",
            crampedscript="S'", scriptscript="SS", crampedscriptscript="SS'"}
local function sizename(fs)
  local b = fs:gsub("'", "")
  return ({D="display", T="text", S="script", SS="scriptscript"})[b]
end
local function cr(fs) if fs:sub(-1) == "'" then return fs end return fs .. "'" end
local function up(fs)
  local c = fs:sub(-1) == "'"
  local b = ({D="S", T="S", S="SS", SS="SS"})[fs:gsub("'", "")]
  return c and b .. "'" or b
end
local function down(fs) return cr(up(fs)) end
local function num(fs) if fs == "D" or fs == "D'" then return "T" .. fs:sub(2) end return up(fs) end
local function den(fs) if fs == "D" or fs == "D'" then return "T'" end return down(fs) end
local NSUB = node.subtypes("noad")

-- glyphs inside a box nucleus (\mathop{lim}, \text{...}): ids, role plain
local function walk_box(list, style)
  local first, last
  for n in node.traverse(list) do
    if n.id == GLYPH0 then
      local v = node.has_attribute(n, ATTR)
      if not v then                       -- a glyph from an earlier (measuring) pass keeps its id and role
        nextid = nextid + 1
        node.set_attribute(n, ATTR, nextid)
        roles[nextid] = {role = "plain", char = n.char, fam = -1, style = sizename(style), fs = style}
        v = nextid
      end
      first = first or v; last = v
    elseif (n.id == HL0 or n.id == VL0) and n.head then
      local f, l = walk_box(n.head, style)
      first = first or f; last = l or last
    end
  end
  return first, last
end


local walk_list
local function walk_kernel(k, style)
  if not k then return nil, nil end
  if k.id == MCHAR then
    nextid = nextid + 1
    node.set_attribute(k, ATTR, nextid)
    roles[nextid] = {role = "plain", char = k.char, fam = k.fam, style = sizename(style), fs = style}
    return nextid, nextid
  elseif k.id == SUBML then
    return walk_list(k.head, style)
  elseif k.id == SUBBOX and k.list then
    return walk_box(k.list, style)
  end
  return nil, nil
end

local function script(kernel, style, base, rel)
  local before = nextid
  local f = walk_kernel(kernel, style)
  if f then
    -- base may be nil: an empty nucleus ({}^{x}) - recorded, never truth
    roles[f].role, roles[f].base = rel, base
    for i = before + 1, nextid do
      if i ~= f and roles[i].role == "plain" then roles[i].role, roles[i].base = "in-" .. rel, base end
    end
  end
end

local function walk_node(n, style)
  if n.id == NOAD then
    local name = NSUB[n.subtype] or ""
    local f, l = walk_kernel(n.nucleus, (name == "over") and cr(style) or style)
    if f and f == l and n.nucleus and n.nucleus.id == MCHAR then        -- declared class of a char atom
      roles[f].cls = (name == "opdisplaylimits" or name == "oplimits" or name == "opnolimits") and "op"
        or ((name == "under" or name == "over" or name == "vcenter") and "ord") or name
    end
    local st = n.subtype
    local limits = (st == 2) or (st == 1 and (style == "D" or style == "D'"))
    script(n.sup, up(style), l, limits and "lim-over" or "sup")
    script(n.sub, down(style), l, limits and "lim-under" or "sub")
    if l then
      roles[l].noad = st
      if n.sup or n.sub then
        local k = n.nucleus and n.nucleus.id
        roles[l].nuc = (st == 1 or st == 2 or st == 3) and "op"
          or ((name == "under" or name == "over" or name == "vcenter") and "box")
          or (k == MCHAR and "char") or (k == SUBML and "list") or "box"
      end
    end
    return f, l
  elseif n.id == FRAC then
    local f = walk_kernel(n.num, num(style)); walk_kernel(n.denom, den(style))
    return f, nil
  elseif n.id == RAD or n.id == ACC then
    local f, l = walk_kernel(n.nucleus, cr(style))
    script(n.sup, up(style), l, "sup"); script(n.sub, down(style), l, "sub")
    if l and (n.sup or n.sub) then roles[l].nuc = (n.id == RAD) and "rad" or "acc" end
    return f, l
  end
  return nil, nil
end

walk_list = function(head, style)
  local first, last
  for n in node.traverse(head) do
    if n.id == STYLE then style = FS[tostring(n.style)] or style
    else
      local f, l = walk_node(n, style)
      first = first or f; last = l or last
    end
  end
  return first, last
end

luatexbase.add_to_callback("pre_mlist_to_hlist_filter", function(head, display_type, pen)
  walk_list(head, (display_type == "display") and "D" or "T")
  return true
end, "fj.texroles.mark")

local GLYPH, HL, VL = node.id("glyph"), node.id("hlist"), node.id("vlist")
local function paint(list)
  local n = list
  while n do
    if n.id == GLYPH then
      local v = node.has_attribute(n, ATTR)
      if v then
        local a = node.new("whatsit", "pdf_literal"); a.mode = 2
        a.data = string.format("%.6f %.6f 1 rg", (v // 256) / 255, (v % 256) / 255)
        local z = node.new("whatsit", "pdf_literal"); z.mode = 2; z.data = "0 g"
        list = node.insert_before(list, n, a); node.insert_after(list, n, z); n = z
      end
    elseif (n.id == HL or n.id == VL) and n.head then
      n.head = paint(n.head)
    end
    n = n.next
  end
  return list
end
luatexbase.add_to_callback("post_mlist_to_hlist_filter", function(head) return paint(head) end, "fj.texroles.paint")

function fj_texroles_write(path)
  local f = io.open(path, "w")
  for i = 1, nextid do local r = roles[i]
    f:write(string.format("%d\t%s\t%s\t%d\t%d\t%s\t%s\t%s\t%s\n", i, r.role, tostring(r.base), r.char, r.fam,
      r.style, r.fs or "-", r.nuc or "-", r.cls or "-")) end
  f:close()
end
