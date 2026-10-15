// Package assets contains the fixed offline report presentation.
package assets

import _ "embed"

//go:embed report.html
var ReportTemplate string
