#set page(
  paper: "us-letter",
  margin: (x: 0.62in, y: 0.52in),
)
#set text(font: "DejaVu Sans", size: 8.8pt, lang: "en")
#set par(leading: 0.48em, spacing: 0.42em, justify: false)

#let section(title) = {
  v(0.42em)
  text(size: 10pt, weight: "bold", title)
  line(length: 100%, stroke: 0.45pt + rgb("#b8c0cc"))
  v(0.16em)
}

#let pill(value) = box(
  inset: (x: 5pt, y: 2.2pt),
  radius: 2.5pt,
  stroke: 0.35pt + rgb("#bcc6d3"),
  fill: rgb("#f4f7fb"),
  text(size: 7.8pt, value),
)

#let render-list(items) = {
  for item in items {
    [- #item]
  }
}

#align(center)[
  #text(size: 17pt, weight: "bold", "{{ NAME }}") \
  #text(size: 10.2pt, "{{ TITLE }}") \
  #text(size: 7.8pt, "{{ LOCATION }} | {{ EMAIL }} | {{ LINKEDIN }} | {{ GITHUB }} | {{ PORTFOLIO }}")
]

#section("Profile")
{{ SUMMARY }}

#section("Targeted Keywords")
#for keyword in ({{ KEYWORDS }}) [
  #pill(keyword)
  h(3pt)
]

#section("Selected Work")
{{ PROJECTS }}

#section("Technical Skills")
{{ SKILLS }}

#section("Education")
{{ EDUCATION }}

#section("Certifications")
{{ CERTIFICATIONS }}
